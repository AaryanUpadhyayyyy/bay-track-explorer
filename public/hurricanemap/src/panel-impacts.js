// Storm impacts and the outbound source links that sit beside them.
//
// Split out of panel.js, which was pinned at its 800-line ceiling: every
// routine edit had to be paid for by deleting a comment somewhere else, which
// is the opposite of what the budget is for.
import { getBillionsFor, getImpactsFor, getMetadata, isDatasetAvailable, windToCategory } from './data.js';
import { escapeHtml, formatStormName, safeExternalUrl } from './html-utils.js';
import { getDateLocale, t } from './i18n.js';
import {
  getDamageMillions,
  getRawDamageText,
  getRawFatalityText,
} from './impact-utils.js';
import {
  BILLIONS_DATASET_STATUS, NCEI_BILLIONS_DATASET_ID,
  formatMillionsUSD, inflateUSD, seriesEndYear,
} from './inflation.js';
import { getBundledDatasetState, getBundledDatasetStatus } from './optional-feeds.js';
import { getSetting } from './settings.js';

// Wikipedia article URL — best-effort. Tries the standard article naming pattern
// for the North Indian Ocean; the user's browser will redirect if Wikipedia has a
// different canonical title.
export function wikipediaUrl(storm) {
  if (!storm.name || storm.name === 'UNNAMED') {
    return `https://en.wikipedia.org/wiki/Special:Search?search=${encodeURIComponent(`${storm.year} North Indian Ocean cyclone season`)}`;
  }
  const name = formatStormName(storm.name);
  // Modern IMD-named systems: "Cyclone <Name>" or "Cyclone <Name> (YYYY)" —
  // search handles both, plus redirects and disambiguation.
  const query = `Cyclone ${name} ${storm.year}`;
  return `https://en.wikipedia.org/wiki/Special:Search?go=Go&search=${encodeURIComponent(query)}`;
}

export function youtubeUrl(storm) {
  const niceName = (!storm.name || storm.name === 'UNNAMED')
    ? `${storm.year} ${storm.basin === 'AS' ? 'Arabian Sea' : 'Bay of Bengal'} cyclone`
    : `${formatStormName(storm.name)} ${storm.year}`;
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(`cyclone ${niceName} landfall India`)}`;
}

/** RSMC New Delhi (IMD) storm report. The per-year "preliminary report" index
 *  lists one PDF per system and takes the year base64-encoded in the query, the
 *  way the site's own year picker builds it. Those indices start at 2013; older
 *  seasons are only in the annual "Report on Cyclonic Disturbances" volumes, so
 *  those years get the annual-report index instead. */
export function imdReportUrl(storm) {
  if (storm.year < 1990) return null;
  if (storm.year >= 2013) {
    const year = typeof btoa === 'function' ? btoa(String(storm.year)) : String(storm.year);
    return `https://rsmcnewdelhi.imd.gov.in/archive-report.php?internal_menu=MjY%3D&year=${encodeURIComponent(year)}`;
  }
  return 'https://rsmcnewdelhi.imd.gov.in/report.php?internal_menu=Mjc%3D';
}

export function renderImpactsBlock(storm, im = getImpactsFor(storm.id)) {
  const rows = [];
  const sources = [];
  if (im) {
    const rawDeaths = getRawFatalityText(im);
    const rawDamage = getRawDamageText(im);
    if (rawDeaths) rows.push(`<div class="im-row"><span class="im-label">${t('impacts.fatalities')}</span><span class="im-value">${escapeHtml(rawDeaths)}</span></div>`);
    if (rawDamage) {
      const mode = getSetting('damageMode');
      const nominalM = getDamageMillions(im);
      let valueHTML = escapeHtml(rawDamage);
      if (mode === 'real' && nominalM != null && storm.year) {
        const r = inflateUSD(nominalM, storm.year);
        if (r) {
          valueHTML = r.currentDollars
            ? `${formatMillionsUSD(r.real)} <span class="im-adj">(${storm.year} USD)</span>`
            : `${formatMillionsUSD(r.real)} <span class="im-adj">(2024 USD · ${formatMillionsUSD(nominalM)} nominal)</span>`;
        }
      } else if (mode === 'nominal' && nominalM != null) {
        valueHTML = `${formatMillionsUSD(nominalM)} <span class="im-adj">(${storm.year || ''} USD)</span>`;
      }
      rows.push(`<div class="im-row"><span class="im-label">${t('impacts.damage')}</span><span class="im-value">${valueHTML}</span></div>`);
    }
    if (rows.length) {
      const safeSourceUrl = safeExternalUrl(im.wiki_url);
      const confidence = ['high', 'medium', 'low'].includes(im.impact_confidence)
        ? im.impact_confidence
        : 'unknown';
      const confidenceText = escapeHtml(t('impacts.confidence', t(`impacts.confidence.${confidence}`)));
      const confidenceTitle = escapeHtml(im.impact_confidence_reason || '');
      const source = safeSourceUrl
        ? `<a href="${safeSourceUrl}" target="_blank" rel="noopener">${t('impacts.wikiSource')}</a>`
        : t('impacts.wikiSource');
      sources.push(`${source} · <span title="${confidenceTitle}">${confidenceText}</span>`);
    }
  }
  const billions = getBillionsFor(storm.id);
  const billionsStatus = getBundledDatasetStatus(getMetadata(), NCEI_BILLIONS_DATASET_ID) || BILLIONS_DATASET_STATUS;
  const billionsState = getBundledDatasetState(billionsStatus, isDatasetAvailable(NCEI_BILLIONS_DATASET_ID));
  const billionsEndYear = seriesEndYear(billionsStatus);
  if (billions && Number.isFinite(billions.cost_cpi_musd)) {
    const deaths = Number.isFinite(billions.deaths)
      ? ` · ${billions.deaths.toLocaleString(getDateLocale())} ${t('impacts.deaths')}`
      : '';
    rows.push(`<div class="im-row"><span class="im-label">${t('impacts.ncei')}</span><span class="im-value">${formatMillionsUSD(billions.cost_cpi_musd)} <span class="im-adj">(2024 USD${deaths})</span></span></div>`);
    sources.push(`<a href="https://www.ncei.noaa.gov/access/billions/" target="_blank" rel="noopener">${t('impacts.nceiSource')}</a>`);
  } else if (billionsState === 'closed' && Number.isInteger(billionsEndYear) && Number(storm.year) > billionsEndYear) {
    rows.push(`<div class="im-row im-row--closed"><span class="im-label">${t('impacts.ncei')}</span><span class="im-value">${t('impacts.nceiClosed', billionsEndYear)}</span></div>`);
    const cite = billionsStatus.retirement_citation;
    const link = (url, key) => (url ? sources.push(`<a href="${url}" target="_blank" rel="noopener">${t(key)}</a>`) : null);
    link(safeExternalUrl(cite?.url), 'impacts.nceiRetirementSource');
    link(safeExternalUrl(cite?.successor?.url), 'impacts.nceiSuccessorSource');
  } else if (billionsState === 'unavailable') {
    rows.push(`<div class="im-row im-row--missing"><span class="im-label">${t('impacts.ncei')}</span><span class="im-value">${t('impacts.nceiUnavailable')}</span></div>`);
  }
  if (!im) {
    rows.push(`<div class="im-row im-row--missing"><span class="im-value">${t('impacts.missingRecord')}</span></div>`);
  }
  if (!rows.length) return '';
  // A death toll for one storm says nothing about how these storms kill, and
  // the best current answer to that is a paper this atlas is not allowed to
  // bundle: CC BY-NC-ND forbids redistributing its figures. So the panel
  // points at it and says why the numbers are not here.
  const study = `<div class="im-study">${t('impacts.fatalityStudy')} <a href="https://doi.org/10.1038/s44304-026-00178-8" target="_blank" rel="noopener">${t('impacts.fatalityStudyLink')}</a></div>`;
  return `
    <h3 class="panel-section-h3">${t('panel.impacts')}</h3>
    <div class="impacts-block">
      ${rows.join('')}
      ${study}
      <div class="im-source">${sources.join(' · ')}</div>
    </div>
  `;
}

/** IMD best-track archive. IMD publishes digitised best tracks for the North
 *  Indian Ocean from 1982 onward, one file per season, from a single index. */
export function imdBestTrackUrl(storm) {
  if (storm.year < 1982) return null;
  return 'https://rsmcnewdelhi.imd.gov.in/report.php?internal_menu=MzM%3D';
}

/** MOSDAC (ISRO) satellite view of the storm. SCORPIO is MOSDAC's cyclone
 *  archive: it takes a year and a cyclone name in its own picker, and carries
 *  INSAT imagery for named systems from 2010 onward. Unnamed systems and older
 *  seasons fall back to MOSDAC's cyclone landing page. */
export function mosdacSatelliteUrl(storm) {
  if (storm.year < 2010) return null;
  if (!storm.name || storm.name === 'UNNAMED') return 'https://www.mosdac.gov.in/cyclone';
  return `https://mosdac.gov.in/scorpio/?year=${storm.year}&cyclone=${encodeURIComponent(formatStormName(storm.name).toUpperCase())}`;
}