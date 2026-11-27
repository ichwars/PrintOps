interface SpoolIconProps {
  color: string;
  isEmpty: boolean;
  size?: number;
}

export function SpoolIcon({ color, isEmpty, size = 32 }: SpoolIconProps) {
  if (isEmpty) {
    return (
      <div
        className="rounded-full border-2 border-dashed border-bambu-dark-tertiary flex items-center justify-center"
        style={{ width: size, height: size }}
      >
        <div className="w-2 h-2 rounded-full bg-bambu-dark-tertiary" />
      </div>
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 32 32">
      {/* Outer ring with white stroke for visibility */}
      <circle cx="16" cy="16" r="14" fill={color} stroke="white" strokeWidth="1.5" strokeOpacity="0.7" />
      {/* Inner shadow/depth */}
      <circle cx="16" cy="16" r="11" fill={color} style={{ filter: 'brightness(0.85)' }} />
    </svg>
  );
}
