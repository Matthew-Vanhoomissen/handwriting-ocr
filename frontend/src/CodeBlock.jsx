// Monospace code with a line-number gutter. `highlight` holds 1-indexed line numbers.
export default function CodeBlock({ code, highlight = [] }) {
  const lines = code.split('\n')
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop()
  const marked = new Set(highlight)

  return (
    <pre className="code">
      {lines.map((line, i) => {
        const n = i + 1
        return (
          <div key={n} className={marked.has(n) ? 'line uncertain' : 'line'}>
            <span className="gutter">{n}</span>
            <span className="text">{line || ' '}</span>
          </div>
        )
      })}
    </pre>
  )
}
