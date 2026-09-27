import Link from "next/link";

export default function HomePage() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center text-center">
      <h1 className="text-4xl font-extrabold text-white sm:text-5xl">
        Book seats. <span className="text-brand-500">In real time.</span>
      </h1>
      <p className="mt-4 max-w-xl text-slate-400">
        Live seat maps, zero double-booking, instant confirmation. Pick an event and watch
        seats update the moment anyone holds, releases, or confirms one.
      </p>
      <div className="mt-8 flex gap-4">
        <Link href="/events" className="btn-primary">
          Browse Events
        </Link>
        <Link href="/signup" className="btn-secondary">
          Create an Account
        </Link>
      </div>
    </div>
  );
}
