// Shared source selector for the Studio analysis tools.
//
// Architecture/Security/Tech Stack/Health each analyse ONE source at a time
// (Repo Chat is the deliberate exception and keeps the sidebar's multi-select).
// The user MUST choose a source before a tool runs, so the control is always
// shown — even when the project has a single source — and starts on a
// "Select a source" placeholder until a choice is made or a remembered one is
// restored.

export default function ToolSourcePicker({ sources, value, onChange }) {
  const list = sources || []

  return (
    <label className="rs-source-picker">
      <span className="rs-source-picker-label">Source</span>
      <select
        className="rs-source-select"
        value={value || ''}
        onChange={(event) => onChange?.(event.target.value)}
        aria-label="Select the source this tool analyses"
      >
        <option value="" disabled>
          Select a source
        </option>
        {list.map((source) => (
          <option key={source.id} value={source.id}>
            {source.title || source.id}
          </option>
        ))}
      </select>
    </label>
  )
}
