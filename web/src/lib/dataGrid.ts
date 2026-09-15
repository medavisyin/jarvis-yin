export function clampGridHeight(
  rowCount: number,
  rowHeight = 36,
  headerHeight = 40,
  max = 420,
  empty = 120,
): number {
  if (rowCount <= 0) return empty;
  return Math.min(max, headerHeight + rowCount * rowHeight);
}
