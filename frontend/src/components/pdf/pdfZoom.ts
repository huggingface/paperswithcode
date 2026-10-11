// Zoom is continuous between these bounds; the buttons step through familiar
// presets, while pinch and the toolbar input accept any value in range.
export const MIN_ZOOM = 0.25;
export const MAX_ZOOM = 4;
const ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4];

export function clampZoom(zoom: number): number {
  return Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
}

export function stepZoom(zoom: number, direction: 1 | -1): number {
  const steps = direction > 0 ? ZOOM_STEPS : [...ZOOM_STEPS].reverse();
  return steps.find((step) => (step - zoom) * direction > 0.005) ?? steps[steps.length - 1];
}
