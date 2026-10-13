export function ProblemList({ problems }: { problems: string[] }) {
  if (problems.length === 0) {
    return null;
  }
  return (
    <ul className="mt-2 list-disc pl-5">
      {problems.map((problem) => (
        <li key={problem}>{problem}</li>
      ))}
    </ul>
  );
}
