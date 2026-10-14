/** Check problems the API reports on a run, word for word. */
export function ProblemList({ problems }: { problems: string[] }) {
  if (problems.length === 0) {
    return null;
  }
  return (
    <ul className="mt-1.5 list-disc pl-5">
      {problems.map((problem) => (
        <li key={problem}>{problem}</li>
      ))}
    </ul>
  );
}
