import type { ReactNode } from 'react';

interface OptionCardProps {
  name: string;
  value: string;
  checked: boolean;
  onSelect: () => void;
  children: ReactNode;
}

export function OptionCard({ name, value, checked, onSelect, children }: OptionCardProps) {
  return (
    <label className="relative flex cursor-pointer flex-col gap-2 rounded-[10px] border border-line bg-surface p-2.5 text-[13px] font-semibold has-[:checked]:border-accent has-[:checked]:shadow-focus has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent">
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onSelect}
        className="sr-only"
      />
      {children}
    </label>
  );
}
