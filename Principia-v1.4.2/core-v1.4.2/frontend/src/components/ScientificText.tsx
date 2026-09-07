import katex from "katex";
import { conciseMeasurements } from "../utils/scientificNumbers";

type ScientificTextProps = {
  value: string;
  className?: string;
  exact?: boolean;
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

function typesetNamedSymbols(source: string): string {
  // Numeric scientific notation is multiplication by a power of ten, not
  // the variable e followed by subtraction. Protect text labels and paths.
  source = source.replace(/\\(?:text|mathrm|operatorname)\{[^{}]*\}|(?<![\w/.:-])(-?\d+(?:\.\d+)?)[eE]([+-]?\d+)(?![\w/.:-])/g,
    (token, mantissa, exponent) => mantissa === undefined ? token : `${mantissa}\\times 10^{${Number(exponent)}}`);
  // Executable ASTs use ASCII names. Translate standalone Greek parameters only
  // inside math, preserving existing commands and explicitly textual labels.
  return source.replace(/\\(?:text|mathrm|operatorname)\{[^{}]*\}|_[A-Za-z0-9]+|(?<![A-Za-z\\])(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|rho|sigma|tau|phi|omega|kappa)(?=_|[^A-Za-z]|$)/g,
    token => token.startsWith("\\") ? token : token.startsWith("_") ? `_{${token.slice(1)}}` : `\\${token}`);
}

// Legacy operator prose sometimes omits math delimiters. Recognize a restricted
// algebra vocabulary, without interpreting ordinary prose, currency, or HTML.
export function normalizeScientificProse(value: string): string {
  const atom = String.raw`(?:\\(?:alpha|beta|gamma|delta|sigma|rho|phi|theta|mu|lambda|kappa)|(?:sqrt|exp|log|ln|atan2)\([^()\n]{1,70}\)|(?:[0-9]+(?:\.[0-9]+)?\s*)?(?:[A-Za-z]|p[xyz]|phi)(?:_\{[^{}\n]+\}|_[A-Za-z0-9]+)?(?:\^(?:\{[^{}\n]+\}|[-+]?\d+))?|[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?)`;
  const equation = new RegExp(String.raw`(?<![\w/])${atom}(?:\s*[=+−*/^<>-]\s*${atom})+(?![\w])`, "g");
  return value.split(delimitedMath).map(fragment => {
    if (/^(?:\$|\\\[|\\\()/.test(fragment)) return fragment;
    return fragment.replace(equation, match => {
      if (!/[=^_]/.test(match)) return match;
      const latex = match.replace(/\bsqrt\(([^()]*)\)/g, String.raw`\sqrt{$1}`)
        .replace(/\b(exp|log|ln|atan2)\(/g, (_, name) => name === "atan2" ? String.raw`\operatorname{atan2}(` : `\\${name}(`)
        .replace(/\bphi\b/g, String.raw`\phi`).replace(/−/g, "-");
      return `$${latex}$`;
    }).replace(/(?<![\w$])([A-Za-z])²/g, (_, symbol) => `$${symbol}^2$`);
  }).join("");
}

/** Render scientific prose while compiling its LaTeX fragments with KaTeX. */
export function ScientificText({ value, className, exact = false }: ScientificTextProps) {
  const fragments = normalizeScientificProse(exact ? value : conciseMeasurements(value)).split(delimitedMath).filter(Boolean);
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
              __html: katex.renderToString(typesetNamedSymbols(math.source), {
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
