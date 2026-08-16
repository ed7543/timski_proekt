interface Props {
  value: string;
  onChange: (value: string) => void;
}

export function ConversationSearchInput({ value, onChange }: Props) {
  return (
    <div className="search-wrap">
      <input
        className="search-input"
        type="text"
        placeholder="Search conversations…"
        defaultValue={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
