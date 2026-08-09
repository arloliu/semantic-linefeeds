// opencode plugin: enforce semantic linefeeds on edit/write via the core CLI.
// Install: copy this file AND scripts/check_linefeeds.py into
// ~/.config/opencode/plugins/ (they must sit side by side), or set
// SEMANTIC_LINEFEEDS_CHECK to the script's absolute path.
import type { Plugin } from "@opencode-ai/plugin"

// Module-private: opencode's loader calls every export as a plugin factory
// and treats the return value as a hooks object,
// so a helper export whose call returns null crashes the server.
// Models with native patch support get an apply_patch tool instead of edit/write;
// its Codex-grammar patch goes to the core's codex parser.
function buildCheck(
  tool: string,
  args: Record<string, unknown>,
): { payload: string; agent: "claude" | "codex" } | null {
  if (tool === "apply_patch") {
    const patch = args.patchText as string | undefined
    if (!patch) return null
    return {
      agent: "codex",
      payload: JSON.stringify({
        tool_name: "apply_patch",
        tool_input: { command: patch },
      }),
    }
  }
  if (tool !== "edit" && tool !== "write") return null
  const filePath = args.filePath as string | undefined
  const text = (tool === "edit" ? args.newString : args.content) as
    | string
    | undefined
  if (!filePath || !text) return null
  return {
    agent: "claude",
    payload: JSON.stringify({
      tool_name: "Edit",
      tool_input: { file_path: filePath, new_string: text },
    }),
  }
}

export const SemanticLinefeeds: Plugin = async ({ $ }) => {
  const script =
    process.env.SEMANTIC_LINEFEEDS_CHECK ??
    new URL("./check_linefeeds.py", import.meta.url).pathname
  return {
    "tool.execute.after": async (input, output) => {
      const args = (input as { args?: Record<string, unknown> }).args ?? {}
      const check = buildCheck(input.tool, args)
      if (!check) return
      let proc
      try {
        proc = await $`printf '%s' ${check.payload} | python3 ${script} --hook ${check.agent}`
          .quiet()
          .nothrow()
      } catch {
        return // advisory tool: a broken checker must never break the agent
      }
      if (proc.exitCode === 2) {
        output.output += `\n\n${proc.stderr.toString().trim()}`
      }
    },
  }
}
