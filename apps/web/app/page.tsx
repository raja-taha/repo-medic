import Link from "next/link";
import { NewTaskForm } from "@/components/NewTaskForm";

export default function HomePage() {
  return (
    <main>
      <section className="hero">
        <p className="fade-up meta">Coding agents · sandboxing · evaluation</p>
        <h1 className="fade-up">RepoMedic</h1>
        <p className="fade-up-delay">
          Turn a GitHub issue into a verified patch: clone into an isolated workspace,
          map the code, reproduce the failure, propose a diff, and hand a human the
          evidence.
        </p>
        <div className="cta-row fade-up-delay">
          <Link className="btn btn-primary" href="#start">
            Start a repair
          </Link>
          <Link className="btn btn-ghost" href="/tasks">
            Open review queue
          </Link>
        </div>
      </section>

      <section className="section" id="start">
        <h2>Dispatch a repair</h2>
        <p className="lede">
          One issue at a time. RepoMedic queues the agent, runs the sandbox loop, and
          parks the result for review.
        </p>
        <div className="grid-2">
          <div className="panel">
            <NewTaskForm />
          </div>
          <div className="panel">
            <h3 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Core loop</h3>
            <ol className="steps">
              <li>
                <span className="dot" />
                <span>Parse acceptance criteria into a repair checklist</span>
              </li>
              <li>
                <span className="dot" />
                <span>Index symbols and search the implicated surface area</span>
              </li>
              <li>
                <span className="dot" />
                <span>Reproduce inside a resource-limited sandbox</span>
              </li>
              <li>
                <span className="dot" />
                <span>Generate a patch, verify tests/lint, emit a PR summary</span>
              </li>
            </ol>
          </div>
        </div>
      </section>
    </main>
  );
}