/**
 * Image preloading utility
 * Preloads images to ensure they're cached before rendering
 */

const pendingPreloads = new Map<string, Promise<void>>();

/**
 * Preloads an image and returns a Promise that resolves when the image is loaded
 * @param imageUrl - The URL of the image to preload
 * @returns Promise that resolves when the image is loaded (or fails gracefully)
 */
export const preloadImage = (imageUrl: string): Promise<void> => {
  if (!imageUrl) return Promise.resolve();

  const pending = pendingPreloads.get(imageUrl);
  if (pending) return pending;

  const preload = new Promise<void>((resolve) => {
    const img = new Image();

    img.onload = () => {
      resolve();
    };

    img.onerror = () => {
      pendingPreloads.delete(imageUrl);
      resolve();
    };

    img.src = imageUrl;
  });
  pendingPreloads.set(imageUrl, preload);
  return preload;
};
