import katex from "katex";

type ScientificTextProps = {
  value: string;
  className?: string;
};

const delimitedMath = /(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$|\$(?!\s)[^$\n]+?\$)/g;

function mathSource(value: string): { source: string; display: boolean } {
  if (value.startsWith("\\[") && value.endsWith("\\]"))
    return { source: value.slice(2, -2), display: true };
  if (value.startsWith("\\(") && value.endsWith("\\)"))
    return { source: value.slice(2, -2), display: false };
  if (value.startsWith("$$") && value.endsWith("$$"))
    return { source: value.slice(2, -2), display: true };
  return { source: value.slice(1, -1), display: false };
}

/** Render scientific prose while compiling its LaTeX fragments with KaTeX. */
export function ScientificText({ value, className }: ScientificTextProps) {
  const fragments = value.split(delimitedMath).filter(Boolean);
  return (
    <span className={className}>
      {fragments.map((fragment, index) => {
        if (!fragment.match(delimitedMath)) return fragment;
        const math = mathSource(fragment);
        return (
          <span
            className={math.display ? "scientific-math display" : "scientific-math"}
            // KaTeX escapes source text and is configured to reject unsafe HTML commands.
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(math.source, {
                displayMode: math.display,
                throwOnError: false,
                strict: "warn",
                trust: false,
                output: "htmlAndMathml",
              }),
            }}
            key={`${index}:${fragment}`}
          />
        );
      })}
    </span>
  );
}
