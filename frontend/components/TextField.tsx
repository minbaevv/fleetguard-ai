import { useId, type InputHTMLAttributes } from "react";

import { inputClass } from "@/lib/styles";

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export function TextField({ label, ...inputProps }: TextFieldProps) {
  const id = useId();

  return (
    <div>
      <label htmlFor={id} className="field-label">
        {label}
        {inputProps.required ? <span className="text-rose-400"> *</span> : null}
      </label>
      <input id={id} {...inputProps} className={inputClass} />
    </div>
  );
}
