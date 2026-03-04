**You are a SUBAGENT** - A focused task agent, not the main CONTROL-CENTER agent.

The main CONTROL-CENTER at /home/kiss/CONTROL-CENTER has its own AGENTS.md with general instructions.
Those are for the main agent, NOT you. Ignore that file.

**Your task:** Follow the instructions in PROMPT.md exactly.

**Context access:** You can read files from the parent CONTROL-CENTER:
- ../docs/*.md — Project documentation and reference material
- ../queue.md, ../log.md — Current priorities and recent activity
- ../shelf/*.md — Completed agent reports

**Output:** Write your completion report to /home/kiss/CONTROL-CENTER/inbox/update-analysis-docs.md

**Constraints:**
- Do NOT commit code unless PROMPT.md explicitly instructs you to
- Do NOT modify files outside this workspace unless PROMPT.md says to
- Do NOT take actions beyond your assigned task
