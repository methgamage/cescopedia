/* Client-side picture handling: resize to max 1600 px and compress (JPEG 82%, or PNG when the picture has transparency).
   Nothing is uploaded here; the compressed Blob is kept in memory until the user submits the proposal. */
window.CescoImages = (function () {
  const MAX_PX = 1600, QUALITY = 0.82;
  const pending = {};            // name -> Blob  (pictures used by the article being edited)
  async function sha10(blob) {
    const buf = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    return Array.from(new Uint8Array(buf)).slice(0, 5).map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  function load(file) {
    return new Promise((res, rej) => {
      const url = URL.createObjectURL(file), im = new Image();
      im.onload = () => { URL.revokeObjectURL(url); res(im); };
      im.onerror = () => { URL.revokeObjectURL(url); rej(new Error("That file is not a readable picture (JPEG, PNG, GIF or WebP).")); };
      im.src = url;
    });
  }
  async function process(file) {
    if (!file || file.size > 40 * 1024 * 1024) throw new Error("Picture is empty or larger than 40 MB.");
    if (!/^image\/(jpeg|png|gif|webp)$/.test(file.type)) throw new Error("Only JPEG, PNG, GIF or WebP pictures are accepted.");
    const im = await load(file);
    let w = im.naturalWidth, h = im.naturalHeight;
    const k = Math.min(1, MAX_PX / Math.max(w, h));
    w = Math.max(1, Math.round(w * k)); h = Math.max(1, Math.round(h * k));
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.drawImage(im, 0, 0, w, h);          // browsers apply EXIF orientation when drawing
    let alpha = false;
    if (file.type !== "image/jpeg") {
      const d = g.getImageData(0, 0, w, h).data;
      for (let i = 3; i < d.length; i += 4) if (d[i] < 250) { alpha = true; break; }
    }
    if (!alpha) { g.globalCompositeOperation = "destination-over"; g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); }
    const type = alpha ? "image/png" : "image/jpeg";
    const blob = await new Promise((r) => c.toBlob(r, type, QUALITY));
    if (!blob) throw new Error("Could not compress that picture.");
    const stem = (file.name || "picture").replace(/\.[^.]*$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) || "picture";
    const name = stem + "-" + (await sha10(blob)) + (alpha ? ".png" : ".jpg");
    return { name, blob, width: w, height: h, bytes: blob.size, url: URL.createObjectURL(blob) };
  }
  return { process, pending };
})();
