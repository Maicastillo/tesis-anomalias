const { queryApi, xbrlApi } = require('sec-api');
const xlsx = require('xlsx');

// ============================================================================
// API KEY
// ============================================================================
// ⚠️ ANTES DE HACER "git add" / "git commit" / "git push":
// pegá tu key de sec-api.io acá abajo para correr el script LOCALMENTE,
// pero volvé a dejar 'PASTE_YOUR_KEY_HERE' antes de subir el archivo al
// repo. Nunca subas este archivo con una key real adentro.
// ============================================================================

const API_TOKEN = 'PASTE_YOUR_KEY_HERE';

if (API_TOKEN === 'PASTE_YOUR_KEY_HERE') {
  console.error(
    '❌ Falta la API key. Pegá tu key de sec-api.io en la constante ' +
    'API_TOKEN antes de correr este script (y sacala de nuevo antes de subir a git).'
  );
  process.exit(1);
}

queryApi.setApiKey(API_TOKEN);
xbrlApi.setApiKey(API_TOKEN);

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function formatGaapTag(tag) {
  if (!tag) return 'N/A';
  return tag
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/^./, str => str.toUpperCase())
    .trim();
}

function formatSegment(segmentArray) {
  if (!segmentArray || !Array.isArray(segmentArray) || segmentArray.length === 0) {
    return 'Consolidated (Total)';
  }

  const segmentNames = segmentArray.map(seg => {
    const rawValue = seg.value || seg.dimension || 'UnknownSegment';
    const cleanName = rawValue.split(':').pop();
    return formatGaapTag(cleanName);
  });

  return segmentNames.join(' | ');
}

// Acepta ticker y filingYear para agregarlos como primeras columnas
function flattenStatement(statementObj, ticker, filingYear) {
  if (!statementObj) return [];
  const rows = [];

  for (const [lineItem, factsArray] of Object.entries(statementObj)) {
    if (Array.isArray(factsArray)) {
      factsArray.forEach(fact => {
        let periodStr = "";
        if (fact.period) {
          if (typeof fact.period === 'string') {
            periodStr = fact.period;
          } else if (fact.period.endDate) {
            periodStr = fact.period.endDate;
          }
        }

        let displayValue = fact.value;
        if (!isNaN(displayValue) && displayValue !== null && displayValue !== "") {
          displayValue = Number(displayValue) / 1000000;
        }

        const segmentContext = formatSegment(fact.segment);

        rows.push({
          'Company': ticker,
          'Document Year': filingYear,
          'Readable Line Item': formatGaapTag(lineItem),
          'Segment / Context': segmentContext,
          'Raw Tag (GAAP)': lineItem,
          'Value (in Millions)': displayValue,
          'Period End': periodStr,
          'Unit': fact.unitRef || 'N/A'
        });
      });
    }
  }
  return rows;
}

// ============================================================================
// CORE EXTRACTION LOGIC
// ============================================================================

async function getFinancialTablesForCompany(ticker, companyName, masterData) {
  console.log(`\n🔍 Finding 10-K/20-F filings for ${companyName} (${ticker})...`);

  const query = {
    query: `ticker:${ticker} AND (formType:"10-K" OR formType:"20-F")`,
    from: '0',
    size: '10',
    sort: [{ filedAt: { order: 'desc' } }]
  };

  try {
    const response = await queryApi.getFilings(query);
    const filings = response.filings;

    if (!filings || filings.length === 0) {
      console.log(`⚠️ No filings found for ${ticker}.`);
      return;
    }

    console.log(`Found ${filings.length} filings for ${ticker}. Extracting data...`);

    for (let i = 0; i < filings.length; i++) {
      const filing = filings[i];
      const filingYear = filing.filedAt.split('-')[0];
      const documentUrl = filing.linkToFilingDetails;

      console.log(`  📥 Processing ${ticker} (${filingYear})...`);

      try {
        const xbrlData = await xbrlApi.xbrlToJson({ htmUrl: documentUrl });

        masterData.Balance.push(...flattenStatement(xbrlData.BalanceSheets, ticker, filingYear));
        masterData.Income.push(...flattenStatement(xbrlData.StatementsOfIncome, ticker, filingYear));
        masterData.CashFlow.push(...flattenStatement(xbrlData.StatementsOfCashFlows, ticker, filingYear));
        masterData.CompIncome.push(...flattenStatement(xbrlData.StatementsOfComprehensiveIncome, ticker, filingYear));
        masterData.Equity.push(...flattenStatement(xbrlData.StatementsOfStockholdersEquity, ticker, filingYear));

      } catch (xbrlError) {
        console.error(`  ⚠️ Failed to parse tables for ${ticker} (${filingYear}). Error: ${xbrlError.message}`);
      }
    }
  } catch (error) {
    console.error(`❌ Error communicating with SEC API for ${ticker}:`, error.message);
  }
}

// ============================================================================
// MASTER EXECUTION
// ============================================================================

async function processAllCompanies() {
  const companies = [
    { name: 'ExxonMobil', ticker: 'XOM' },
    { name: 'Chevron', ticker: 'CVX' },
    { name: 'ConocoPhillips', ticker: 'COP' },
    { name: 'Occidental Petroleum', ticker: 'OXY' },
    { name: 'Shell', ticker: 'SHEL' },
    { name: 'BP', ticker: 'BP' },
    { name: 'TotalEnergies', ticker: 'TTE' },
    { name: 'Equinor', ticker: 'EQNR' },
    { name: 'EOG Resources', ticker: 'EOG' },
    { name: 'Pioneer Natural Resources', ticker: 'PXD' }
  ];

  const masterData = {
    Balance: [],
    Income: [],
    CashFlow: [],
    CompIncome: [],
    Equity: []
  };

  console.log("🚀 Starting batch financial data extraction...");

  for (const company of companies) {
    await getFinancialTablesForCompany(company.ticker, company.name, masterData);

    console.log("Waiting 2 seconds before the next company...");
    await new Promise(resolve => setTimeout(resolve, 2000));
  }

  console.log("\n📦 Compiling Master Excel File...");

  const workbook = xlsx.utils.book_new();

  const addSheetIfDataExists = (dataArray, sheetName) => {
    if (dataArray && dataArray.length > 0) {
      const worksheet = xlsx.utils.json_to_sheet(dataArray);
      xlsx.utils.book_append_sheet(workbook, worksheet, sheetName);
    }
  };

  addSheetIfDataExists(masterData.Balance, 'Balance Sheet');
  addSheetIfDataExists(masterData.Income, 'Income Statement');
  addSheetIfDataExists(masterData.CashFlow, 'Cash Flow');
  addSheetIfDataExists(masterData.CompIncome, 'Comp Income');
  addSheetIfDataExists(masterData.Equity, 'Equity');

  const finalFileName = 'Master_Energy_Financials.xlsx';
  xlsx.writeFile(workbook, finalFileName);

  console.log(`🎉 Complete! All data saved into a single file: ${finalFileName}`);
}

// Execute
processAllCompanies();
