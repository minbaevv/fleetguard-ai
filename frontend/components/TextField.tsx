import { useId, type InputHTMLAttributes } from "react";

import { inputClass } from "@/lib/styles";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function TextField({ label, ...inputProps }: TextFieldProps) {
  const id = useId();

  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {label}
        {inputProps.required ? <span className="text-red-600"> *</span> : null}
      </label>
      <input id={id} {...inputProps} className={inputClass} />
    </div>
  );
}
