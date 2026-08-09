import { expect, test } from "bun:test"
import SemanticLinefeeds, { buildPayload } from "./semantic-linefeeds"

test("edit tool produces a Claude-shaped payload", () => {
  const p = buildPayload("edit", { filePath: "/x/doc.go", newString: "// hi" })
  expect(JSON.parse(p!)).toEqual({
    tool_name: "Edit",
    tool_input: { file_path: "/x/doc.go", new_string: "// hi" },
  })
})

test("write tool uses content", () => {
  const p = buildPayload("write", { filePath: "/x/a.md", content: "Prose." })
  expect(JSON.parse(p!).tool_input.new_string).toBe("Prose.")
})

test("other tools and empty args are ignored", () => {
  expect(buildPayload("bash", { command: "ls" })).toBeNull()
  expect(buildPayload("edit", {})).toBeNull()
})

// A fake Bun shell: a template tag whose result supports .quiet().nothrow().
function fakeShell(exitCode: number, stderr: string) {
  const result = { exitCode, stderr, stdout: "" }
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

async function runAfterHook(exitCode: number, stderr: string, tool = "edit") {
  const { $, calls } = fakeShell(exitCode, stderr)
  const hooks = await SemanticLinefeeds({ $ } as never)
  const output = { title: "", output: "original output", metadata: {} }
  await hooks["tool.execute.after"]!(
    {
      tool,
      sessionID: "s",
      callID: "c",
      args: { filePath: "/x/doc.go", newString: "// text" },
    } as never,
    output as never,
  )
  return { output, calls }
}

test("after-hook appends stderr to tool output on exit 2", async () => {
  const { output } = await runAfterHook(2, "semantic-linefeeds: 1 issue(s)")
  expect(output.output).toContain("original output")
  expect(output.output).toContain("semantic-linefeeds: 1 issue(s)")
})

test("after-hook leaves output alone on exit 0", async () => {
  const { output } = await runAfterHook(0, "")
  expect(output.output).toBe("original output")
})

test("after-hook never spawns for non-target tools", async () => {
  const { output, calls } = await runAfterHook(2, "should not appear", "bash")
  expect(output.output).toBe("original output")
  expect(calls.length).toBe(0)
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
