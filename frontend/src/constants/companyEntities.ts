export const COMPANY_ENTITIES = [
  "上海山途远智信息科技有限公司",
  "山途远智（上海）企业服务有限公司"
] as const;

export type BuyerMatchStatus = "exact" | "partial" | "none";

const TITLE_NOISE_PATTERN = /[\s:：,，.。()（）\[\]【】《》<>“”"']/g;

export function normalizeCompanyTitle(value: string): string {
  return value.replace(/购买方/g, "").replace(/付款方/g, "").replace(/名称/g, "").replace(TITLE_NOISE_PATTERN, "");
}

export function buyerMatchStatus(buyer: string): BuyerMatchStatus {
  const recognized = normalizeCompanyTitle(buyer);
  if (!recognized) return "none";
  const allowed = COMPANY_ENTITIES.map(normalizeCompanyTitle);
  if (allowed.includes(recognized)) return "exact";
  return allowed.some((company) => company.includes(recognized) || recognized.includes(company)) ? "partial" : "none";
}

export function isDifferentAllowedBuyer(buyer: string, currentCompany: string): boolean {
  return buyerMatchStatus(buyer) === "exact" && normalizeCompanyTitle(buyer) !== normalizeCompanyTitle(currentCompany);
}
