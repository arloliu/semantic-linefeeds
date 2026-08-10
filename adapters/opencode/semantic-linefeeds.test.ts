import { expect, test } from "bun:test"
import * as mod from "./semantic-linefeeds"

const { SemanticLinefeeds } = mod

// opencode's loader calls EVERY module export as a plugin factory,
// and it uses the return value as a hooks object;
// an export that returns null crashes the server on the next hook dispatch.
test("the module exposes exactly one loader-safe plugin export", async () => {
  expect(Object.keys(mod)).toEqual(["SemanticLinefeeds"])
  const hooks = await (SemanticLinefeeds as unknown as (input: unknown) => Promise<unknown>)({})
  expect(hooks).toBeTruthy()
  expect(typeof hooks).toBe("object")
})

// A fake Bun shell: a template tag whose result supports .quiet().nothrow().
function fakeShell(exitCode: number, stderr: string, stdout = "") {
  const result = { exitCode, stderr, stdout }
  const chain = {
    quiet: () => chain,
    nothrow: () => Promise.resolve(result),
  }
  const calls: unknown[][] = []
  const $ = (...a: unknown[]) => {
    calls.push(a)
    return chain
  }
  return { $, calls }
}

async function runAfterHook(
  exitCode: number,
  stderr: string,
  tool = "edit",
  args: Record<string, unknown> = { filePath: "/x/doc.go", newString: "// text" },
  stdout = "",
) {
  const { $, calls } = fakeShell(exitCode, stderr, stdout)
  const hooks = await SemanticLinefeeds({ $ } as never)
  const output = { title: "", output: "original output", metadata: {} }
  await hooks["tool.execute.after"]!(
    { tool, sessionID: "s", callID: "c", args } as never,
    output as never,
  )
  return { output, calls }
}

// The checker invocation is `printf '%s' ${payload} | python3 ${script} ...`,
// so the payload is the first value interpolated into the template call.
function payloadFrom(calls: unknown[][]) {
  return JSON.parse(calls[0]![1] as string)
}

test("an edit spawns the checker with a Claude-shaped payload", async () => {
  const { calls } = await runAfterHook(0, "", "edit", {
    filePath: "/x/doc.go",
    newString: "// hi",
  })
  expect(payloadFrom(calls)).toEqual({
    tool_name: "Edit",
    tool_input: { file_path: "/x/doc.go", new_string: "// hi" },
  })
})

test("a write's content becomes new_string in the payload", async () => {
  const { calls } = await runAfterHook(0, "", "write", {
    filePath: "/x/a.md",
    content: "Prose.",
  })
  expect(payloadFrom(calls).tool_input.new_string).toBe("Prose.")
})

test("an apply_patch routes the patch text to the codex checker", async () => {
  const patch = "*** Begin Patch\n*** Add File: doc.go\n+// x. y\n*** End Patch"
  const { calls } = await runAfterHook(0, "", "apply_patch", { patchText: patch })
  expect(payloadFrom(calls)).toEqual({
    tool_name: "apply_patch",
    tool_input: { command: patch },
  })
  expect(calls[0]![3]).toBe("codex")
})

test("an apply_patch with findings appends stderr on exit 2", async () => {
  const { output } = await runAfterHook(2, "semantic-linefeeds: 1 issue(s)", "apply_patch", {
    patchText: "*** Begin Patch\n*** End Patch",
  })
  expect(output.output).toContain("semantic-linefeeds: 1 issue(s)")
})

test("an edit still routes to the claude checker", async () => {
  const { calls } = await runAfterHook(0, "")
  expect(calls[0]![3]).toBe("claude")
})

test("other tools and empty args never spawn the checker", async () => {
  const bash = await runAfterHook(2, "should not appear", "bash", { command: "ls" })
  expect(bash.output.output).toBe("original output")
  expect(bash.calls.length).toBe(0)
  const empty = await runAfterHook(2, "should not appear", "edit", {})
  expect(empty.calls.length).toBe(0)
})

test("after-hook appends stderr to tool output on exit 2", async () => {
  const { output } = await runAfterHook(2, "semantic-linefeeds: 1 issue(s)")
  expect(output.output).toContain("original output")
  expect(output.output).toContain("semantic-linefeeds: 1 issue(s)")
})

test("after-hook leaves output alone on exit 0", async () => {
  const { output } = await runAfterHook(0, "")
  expect(output.output).toBe("original output")
})

// The core delivers non-blocking findings as exit 0 with a JSON object on stdout,
// because exit-0 stderr reaches no model in the native hosts.
// An adapter that reads stderr alone therefore drops every advisory.
const ADVICE = "semantic-linefeeds: 1 issue(s)\n  [long] line 1: advisory"

function advisoryPayload(context: string) {
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "PostToolUse",
      additionalContext: context,
    },
  })
}

test("an exit-0 advisory reaches the tool output", async () => {
  const { output } = await runAfterHook(
    0, "", "edit",
    { filePath: "/x/doc.md", newString: "// text" },
    advisoryPayload(ADVICE),
  )
  expect(output.output).toContain("original output")
  expect(output.output).toContain("[long] line 1: advisory")
})

test("the transport envelope never reaches the model", async () => {
  const { output } = await runAfterHook(
    0, "", "edit",
    { filePath: "/x/doc.md", newString: "// text" },
    advisoryPayload(ADVICE),
  )
  expect(output.output).not.toContain("hookSpecificOutput")
  expect(output.output).not.toContain("additionalContext")
})

test("an apply_patch advisory reaches the tool output too", async () => {
  const { output } = await runAfterHook(
    0, "", "apply_patch",
    { patchText: "*** Begin Patch\n*** End Patch" },
    advisoryPayload(ADVICE),
  )
  expect(output.output).toContain("[long] line 1: advisory")
})

// A checker that dies, warns, or changes its output shape must leave the agent working.
// This adapter is advisory,
// and nothing it does is worth failing an edit over.
// But silence would disable advice without saying so,
// and only a human can repair a mismatched install.
test("unparseable exit-0 stdout says so without echoing it", async () => {
  const { output } = await runAfterHook(
    0, "", "edit",
    { filePath: "/x/doc.md", newString: "// text" },
    "not json at all",
  )
  expect(output.output).toContain("original output")
  expect(output.output).toContain("could not read")
  expect(output.output).not.toContain("not json at all")
})

test("exit-0 JSON without the expected shape says so too", async () => {
  const { output } = await runAfterHook(
    0, "", "edit",
    { filePath: "/x/doc.md", newString: "// text" },
    JSON.stringify({ hookSpecificOutput: { hookEventName: "PostToolUse" } }),
  )
  expect(output.output).toContain("could not read")
})

test("the transport warning is said once per session, not once per edit", async () => {
  const { $ } = fakeShell(0, "", "not json at all")
  const hooks = await SemanticLinefeeds({ $ } as never)
  const args = { filePath: "/x/doc.md", newString: "// text" }
  const outputs = []
  for (let i = 0; i < 3; i++) {
    const output = { title: "", output: "original output", metadata: {} }
    await hooks["tool.execute.after"]!(
      { tool: "edit", sessionID: "s", callID: "c", args } as never,
      output as never,
    )
    outputs.push(output.output)
  }
  expect(outputs[0]).toContain("could not read")
  expect(outputs[1]).toBe("original output")
  expect(outputs[2]).toBe("original output")
})

test("a fresh session warns again", async () => {
  // The flag lives on the plugin instance, so it must not outlive one.
  for (let i = 0; i < 2; i++) {
    const { output } = await runAfterHook(
      0, "", "edit",
      { filePath: "/x/doc.md", newString: "// text" },
      "not json at all",
    )
    expect(output.output).toContain("could not read")
  }
})

test("an empty advisory string is not appended as blank space", async () => {
  const { output } = await runAfterHook(
    0, "", "edit",
    { filePath: "/x/doc.md", newString: "// text" },
    advisoryPayload("   "),
  )
  expect(output.output).toBe("original output")
})

// Findings of mixed kinds exit 2 and travel as one report on stderr.
// The core writes nothing to stdout there,
// but the adapter must not append twice even if it did,
// since a duplicated report reads as two problems.
test("a blocking result appends the report exactly once", async () => {
  const { output } = await runAfterHook(
    2, "semantic-linefeeds: 2 issue(s)", "edit",
    { filePath: "/x/doc.md", newString: "// text" },
    advisoryPayload(ADVICE),
  )
  expect(output.output).toContain("semantic-linefeeds: 2 issue(s)")
  expect(output.output).not.toContain("[long] line 1: advisory")
})

test("non-0/non-2 subprocess exits leave output alone", async () => {
  const { output } = await runAfterHook(127, "python3: command not found")
  expect(output.output).toBe("original output")
})

test("a throwing shell is swallowed", async () => {
  const $ = () => {
    throw new Error("spawn failed")
  }
  const hooks = await SemanticLinefeeds({ $ } as never)
  const output = { title: "", output: "original output", metadata: {} }
  await hooks["tool.execute.after"]!(
    {
      tool: "edit",
      sessionID: "s",
      callID: "c",
      args: { filePath: "/x/doc.go", newString: "// hi" },
    } as never,
    output as never,
  )
  expect(output.output).toBe("original output")
})
