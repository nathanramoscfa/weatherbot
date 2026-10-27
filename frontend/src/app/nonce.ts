// frontend/src/app/nonce.ts
declare global {
  var __webpack_nonce__: string | undefined;
}

export function readCspNonce(doc: Document | undefined = globalThis.document): string | undefined {
  if (!doc) {
    return undefined;
  }
  const meta = doc.querySelector<HTMLMetaElement>('meta[property="csp-nonce"]');
  if (!meta) {
    return undefined;
  }
  const propNonce = meta.nonce;
  if (typeof propNonce === "string" && propNonce.length > 0) {
    return propNonce;
  }
  const attrNonce = meta.getAttribute("nonce");
  if (typeof attrNonce === "string" && attrNonce.length > 0) {
    return attrNonce;
  }
  return undefined;
}

export function initCspNonce(doc: Document | undefined = globalThis.document): string | undefined {
  const nonce = readCspNonce(doc);
  globalThis.__webpack_nonce__ = nonce;
  return nonce;
}
