import { ScientificText } from './ScientificText';

type Explanation = { summary?: string; explanation?: string; explanation_label?: string; implication?: string; boundaries?: string[]; next_check?: string };
export function PlainLanguageInterpretation({ value, fallback = '', title = 'Plain-language interpretation' }: { value?: Explanation; fallback?: string; title?: string }) {
  const summary = value?.summary || fallback;
  if (!summary) return null;
  const paragraphs = [
    [value?.explanation_label || 'Meaning', value?.explanation],
    ['Practical meaning', value?.implication],
  ].filter(([, body], index, all) => body && body !== summary && all.findIndex(([, prior]) => prior === body) === index);
  return <section className="plain-language-interpretation"><h3>{title}</h3>
    <ScientificText value={summary} />
    {paragraphs.map(([label, body]) => <div key={label}><h4>{label}</h4><ScientificText value={body!} /></div>)}
    {value?.boundaries?.length ? <details className="interpretation-boundaries"><summary>Scope and alternative explanations</summary>{value.boundaries.map((boundary, index) => <ScientificText key={index} value={boundary} />)}</details> : null}
    {value?.next_check && value.next_check !== summary ? <div><h4>Next validation</h4><ScientificText value={value.next_check} /></div> : null}
  </section>;
}
