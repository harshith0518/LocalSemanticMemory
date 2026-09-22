import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  const units = ["bytes", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  // Keep rounding near a boundary from displaying four digits in a smaller unit.
  if (
    unit > 0 &&
    Math.round(value * 100) / 100 >= 1000 &&
    unit < units.length - 1
  ) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${bytes === 1 ? "byte" : units[unit]}`;
}
