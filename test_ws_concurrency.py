"""
WebSocket concurrency tests — race condition + venue/capacity enforcement.

UPDATED: Dynamically creates distinct test accounts for all 50 simulated
clients so that `held_by_user_id` in room broadcasts uniquely identifies
the single real winner.
"""

import asyncio
import json
import time
import httpx
import websockets

BASE_HTTP_URL = "http://127.0.0.1:8000"
EVENT_ID = 2
WS_URL = f"ws://127.0.0.1:8000/ws/events/{EVENT_ID}"
CONCURRENT_USERS = 50
RESPONSE_TIMEOUT = 8.0

TEST_PASSWORD = "testpassword123"


async def create_and_login_user(client: httpx.AsyncClient, user_index: int) -> tuple[str, int]:
    """
    Creates a unique test account for each worker and returns (token, user_id).
    """
    email = f"race_user_{user_index}@test.com"
    
    # 1. Signup
    signup_resp = await client.post(f"{BASE_HTTP_URL}/signup", json={
        "email": email,
        "password": TEST_PASSWORD,
        "role": "buyer",
    })
    
    # 2. Login
    login_resp = await client.post(f"{BASE_HTTP_URL}/login", data={
        "username": email, 
        "password": TEST_PASSWORD
    })
    
    if login_resp.status_code != 200:
        raise RuntimeError(f"Login failed for {email}: {login_resp.text}")
        
    token = login_resp.json()["access_token"]
    
    # Extract user_id from signup or decode token/endpoint
    # If your signup returns the user object:
    user_id = signup_resp.json().get("id")
    
    # Fallback: fetch current user profile if id wasn't in signup
    if not user_id:
        me_resp = await client.get(
            f"{BASE_HTTP_URL}/me", 
            headers={"Authorization": f"Bearer {token}"}
        )
        user_id = me_resp.json()["id"]
        
    return token, user_id


# ============================================================================
# READ MESSAGES IN A LOOP, FILTERING FOR MY SPECIFIC USER ID & SEAT ID
# ============================================================================
async def wait_for_my_response(
    ws, 
    my_seat_id: int, 
    my_user_id: int, 
    timeout: float = RESPONSE_TIMEOUT
) -> dict:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout

    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f"No response about seat_id={my_seat_id} within {timeout}s")

        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        msg = json.loads(raw)

        # 1. SUCCESS: Must match BOTH seat_id AND held_by_user_id
        if (
            msg.get("event") == "SEAT_HELD" 
            and msg.get("seat_id") == my_seat_id 
            and msg.get("held_by_user_id") == my_user_id
        ):
            return msg

        # 2. REJECTION: Matching error message for this seat
        if msg.get("event") == "ERROR" and f"Seat {my_seat_id} " in msg.get("message", ""):
            return msg

        # Broadcast was for another user's win -> keep listening for my ERROR or confirmation


# ============================================================================
# DISCOVERY
# ============================================================================
async def discover_test_data(client: httpx.AsyncClient):
    event_resp = await client.get(f"{BASE_HTTP_URL}/events/{EVENT_ID}")
    if event_resp.status_code != 200:
        raise RuntimeError(f"Event {EVENT_ID} not found ({event_resp.status_code}): {event_resp.text}")
    venue_id = event_resp.json()["venue_id"]
    print(f"   Event {EVENT_ID} belongs to venue_id={venue_id}")

    seat_map_resp = await client.get(f"{BASE_HTTP_URL}/events/{EVENT_ID}/seats")
    if seat_map_resp.status_code != 200:
        raise RuntimeError(f"Could not fetch seat map for event {EVENT_ID}: {seat_map_resp.text}")
    all_seats = seat_map_resp.json()["seats"]

    usable_seats = [s for s in all_seats if s["status"] == "AVAILABLE" and float(s["price"]) > 0]

    if not usable_seats:
        raise RuntimeError(f"No AVAILABLE priced seats for event {EVENT_ID}.")

    print(f"   Found {len(usable_seats)} AVAILABLE, priced seat(s): {[s['seat_id'] for s in usable_seats]}")

    venues_resp = await client.get(f"{BASE_HTTP_URL}/venues/")
    foreign_seat_id = None
    for v in venues_resp.json():
        if v["id"] == venue_id:
            continue
        other_seats_resp = await client.get(f"{BASE_HTTP_URL}/venues/{v['id']}/seats")
        other_seats = other_seats_resp.json()
        if other_seats:
            foreign_seat_id = other_seats[0]["id"]
            print(f"   Found a foreign seat: seat_id={foreign_seat_id} (venue_id={v['id']})")
            break

    return venue_id, usable_seats, foreign_seat_id


# ============================================================================
# TEST 1: RACE CONDITION
# ============================================================================
async def simulate_race_user(
    user_index: int, 
    token: str, 
    user_id: int, 
    seat_id: int, 
    start_barrier: asyncio.Event
):
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"action": "auth", "token": token}))
            init = json.loads(await ws.recv())
            if init.get("event") != "CONNECTED":
                return {"user_index": user_index, "error": f"Auth failed: {init}"}

            await start_barrier.wait()

            await ws.send(json.dumps({"action": "hold_seat", "seat_id": seat_id, "price_paid": 999999.0}))
            response = await wait_for_my_response(ws, seat_id, user_id)
            return {"user_index": user_index, "response": response}
    except Exception as e:
        return {"user_index": user_index, "error": repr(e)}


async def run_race_condition_test(users_info: list[tuple[str, int]], target_seat_id: int):
    print(f"\n🚀 TEST 1: Race condition — {CONCURRENT_USERS} unique users fighting over seat_id={target_seat_id}...")

    start_barrier = asyncio.Event()
    tasks = [
        asyncio.create_task(simulate_race_user(i, token, user_id, target_seat_id, start_barrier)) 
        for i, (token, user_id) in enumerate(users_info)
    ]
    await asyncio.sleep(1)

    print("⚡ Releasing barrier — all clients fire 'hold_seat' simultaneously...")
    start_time = time.time()
    start_barrier.set()
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start_time

    successful_holds = [r for r in results if r.get("response", {}).get("event") == "SEAT_HELD"]
    errors = [r for r in results if r.get("response", {}).get("event") == "ERROR"]
    exceptions = [r for r in results if "error" in r]

    print(f"Elapsed: {elapsed:.3f}s | SEAT_HELD: {len(successful_holds)} | ERROR: {len(errors)} | exceptions: {len(exceptions)}")

    if errors:
        print(f"   Example ERROR message: {errors[0]['response']['message']}")

    if len(successful_holds) == 1 and len(errors) == CONCURRENT_USERS - 1 and not exceptions:
        print("✅ PASS: Exactly one client secured the seat; the other 49 were correctly rejected.")
    else:
        print(f"❌ FAIL: Expected 1 success and 49 errors. Got {len(successful_holds)} successes.")


# ============================================================================
# TEST 2: CAPACITY / VENUE ENFORCEMENT
# ============================================================================
async def simulate_capacity_user(user_index: int, token: str, user_id: int, seat_id: int, start_barrier: asyncio.Event):
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"action": "auth", "token": token}))
            init = json.loads(await ws.recv())
            if init.get("event") != "CONNECTED":
                return {"user_index": user_index, "error": f"Auth failed: {init}"}

            await start_barrier.wait()

            await ws.send(json.dumps({"action": "hold_seat", "seat_id": seat_id, "price_paid": 1.0}))
            response = await wait_for_my_response(ws, seat_id, user_id)
            return {"user_index": user_index, "seat_id": seat_id, "response": response}
    except Exception as e:
        return {"user_index": user_index, "seat_id": seat_id, "error": repr(e)}


async def run_capacity_test(users_info: list[tuple[str, int]], real_seat_ids: list[int], foreign_seat_id: int | None):
    print(f"\n🚀 TEST 2: Capacity/venue enforcement — {len(real_seat_ids)} real seat(s)"
          + (" + 1 foreign seat" if foreign_seat_id else "") + "...")

    start_barrier = asyncio.Event()
    all_seat_attempts = list(real_seat_ids)
    if foreign_seat_id is not None:
        all_seat_attempts.append(foreign_seat_id)

    tasks = [
        asyncio.create_task(simulate_capacity_user(i, token, user_id, seat_id, start_barrier))
        for i, (seat_id, (token, user_id)) in enumerate(zip(all_seat_attempts, users_info))
    ]
    await asyncio.sleep(1)
    start_barrier.set()
    results = await asyncio.gather(*tasks)

    real_results = results[:len(real_seat_ids)]
    foreign_result = results[-1] if foreign_seat_id is not None else None

    successful_real = [r for r in real_results if r.get("response", {}).get("event") == "SEAT_HELD"]

    print(f"Real seats held successfully: {len(successful_real)} / {len(real_seat_ids)}")

    if len(successful_real) == len(real_seat_ids):
        print("✅ PASS: Every legitimate seat in this venue could be held.")

    if foreign_result is not None:
        foreign_response = foreign_result.get("response", {})
        print(f"Foreign seat (id={foreign_seat_id}) response: {foreign_response}")
        if foreign_response.get("event") == "ERROR" and "venue" in foreign_response.get("message", "").lower():
            print("✅ PASS: A seat from a different venue was correctly rejected.")


# ============================================================================
# MAIN
# ============================================================================
async def main():
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        try:
            print("🔑 Provisioning 50 unique test user accounts...")
            users_info = await asyncio.gather(*[
                create_and_login_user(http_client, i) for i in range(CONCURRENT_USERS)
            ])
            print(f"✅ Created and authenticated {len(users_info)} distinct accounts.")
            
            print("🔎 Discovering real event/venue/seat data from the live API...")
            venue_id, usable_seats, foreign_seat_id = await discover_test_data(http_client)
        except Exception as e:
            print(f"❌ Setup error: {e!r}")
            return

    target_seat_id = usable_seats[0]["seat_id"]
    await run_race_condition_test(users_info, target_seat_id)

    async with httpx.AsyncClient() as http_client:
        _, refreshed_usable_seats, _ = await discover_test_data(http_client)

    remaining_seat_ids = [s["seat_id"] for s in refreshed_usable_seats if s["seat_id"] != target_seat_id]

    if remaining_seat_ids:
        await run_capacity_test(users_info, remaining_seat_ids, foreign_seat_id)


if __name__ == "__main__":
    asyncio.run(main())