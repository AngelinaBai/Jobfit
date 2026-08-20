const $ = id => document.getElementById(id);

function firstText(selectors) {
  for (const selector of selectors) {
    const el = document.querySelector(selector);
    const text = el?.innerText?.trim() || el?.textContent?.trim();
    if (text) return text;
  }
  return "";
}

function extractJob() {
  const host = location.hostname.toLowerCase();
  let platform = "company-site";
  if (host.includes("linkedin.com")) platform = "linkedin";
  else if (host.includes("joinhandshake.com")) platform = "handshake";
  else if (host.includes("12twenty.com")) platform = "12twenty";

  const title = firstText([
    "h1.t-24", ".job-details-jobs-unified-top-card__job-title h1",
    "[data-hook='job-title']", "h1"
  ]);
  const company = firstText([
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name", "[data-hook='employer-name']",
    "[class*='company']", "[class*='employer']"
  ]);
  const locationText = firstText([
    ".job-details-jobs-unified-top-card__primary-description-container",
    ".jobs-unified-top-card__bullet", "[data-hook='job-location']",
    "[class*='location']"
  ]);
  const description = firstText([
    "#job-details", ".jobs-description-content__text",
    "[data-hook='job-description']", "[class*='job-description']",
    "main"
  ]);
  return {title, company, location: locationText, description, job_url: location.href, platform};
}

async function load() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  const [{result}] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: extractJob});
  $("title").value = result.title;
  $("company").value = result.company;
  $("location").value = result.location;
  $("description").value = result.description;
  window.extracted = result;
}

$("save").addEventListener("click", async () => {
  $("status").textContent = "Saving…";
  const payload = {
    ...(window.extracted || {}),
    title: $("title").value,
    company: $("company").value,
    location: $("location").value,
    description: $("description").value
  };
  try {
    const response = await fetch("http://127.0.0.1:8000/api/import-job", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Import failed");
    $("status").textContent = body.created ? `Saved as JobFit #${body.job_id}` : `Updated JobFit #${body.job_id}`;
  } catch (error) {
    $("status").textContent = `Could not reach JobFit: ${error.message}. Start jobfit-web first.`;
  }
});

load().catch(error => { $("status").textContent = `Could not read this page: ${error.message}`; });
