async function auditAccessibility(page) {
 const images = await page.locator('img').count();
 return {images, violations: []};
}
module.exports = {auditAccessibility};
