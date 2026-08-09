// opencode plugin: enforce semantic linefeeds on edit/write via the core CLI.
// Install: copy this file AND scripts/check_linefeeds.py into
// ~/.config/opencode/plugins/ (they must sit side by side), or set
// SEMANTIC_LINEFEEDS_CHECK to the script's absolute path.
import type { Plugin } from "@opencode-ai/plugin"

export function buildPayload(
  tool: string,
  args: Record<string, unknown>,
): string | null {
  if (tool !== "edit" && tool !== "write") return null
  const filePath = args.filePath as string | undefined
  const text = (tool === "edit" ? args.newString : args.content) as
    | string
    | undefined
  if (!filePath || !text) return null
  return JSON.stringify({
    tool_name: "Edit",
    tool_input: { file_path: filePath, new_string: text },
  })
}

export const SemanticLinefeeds: Plugin = async ({ $ }) => {
  const script =
    process.env.SEMANTIC_LINEFEEDS_CHECK ??
    new URL("./check_linefeeds.py", import.meta.url).pathname
  return {
    "tool.execute.after": async (input, output) => {
      const args = (input as { args?: Record<string, unknown> }).args ?? {}
      const payload = buildPayload(input.tool, args)
      if (!payload) return
      let proc
      try {
        proc = await $`printf '%s' ${payload} | python3 ${script} --hook claude`
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

export default SemanticLinefeeds
