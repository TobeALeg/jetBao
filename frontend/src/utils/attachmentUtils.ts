export function looksLikeImage(filename: string): boolean {
  return /\.(png|jpe?g|webp|gif|bmp)$/i.test(filename);
}

export function looksLikePdf(filename: string): boolean {
  return /\.pdf$/i.test(filename);
}
