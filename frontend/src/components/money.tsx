export function Money({ value }: { value: number | string }) { return <span className="font-mono">¥{Number(value).toFixed(2)}</span>; }
