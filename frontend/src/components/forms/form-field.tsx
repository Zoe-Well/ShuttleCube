import type { InputHTMLAttributes, ReactNode } from "react";
export function FormField({ label, error, children }: { label: string; error?: string; children: ReactNode }) { return <label className="grid gap-1.5 text-sm font-medium"><span>{label}</span>{children}{error && <small className="text-red-600">{error}</small>}</label>; }
export function Input(props: InputHTMLAttributes<HTMLInputElement>) { return <input className="field" {...props} />; }
