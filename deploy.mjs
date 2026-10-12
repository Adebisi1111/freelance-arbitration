// Deploy FreelanceArbitration to GenLayer Bradbury (chain 4221) via genlayer-js.
// Code is passed as a UTF-8 string (Uint8Array makes gas estimation revert on
// Bradbury); receipts are polled with waitUntil:'finalized'.
import { createClient, createAccount } from 'genlayer-js';
import { testnetBradbury } from 'genlayer-js/chains';
import fs from 'fs';

const PK = process.env.DEPLOY_PK;
if (!PK) { console.error('DEPLOY_PK not set'); process.exit(1); }

const CONTRACT = '/home/administrator/freelance-arbitration/contracts/freelance_arbitration.py';

async function main() {
  const account = createAccount(PK);
  const client = createClient({ chain: testnetBradbury, account });
  const code = fs.readFileSync(CONTRACT, 'utf8');
  console.log('Contract bytes:', code.length);

  const tx = await client.deployContract({ code });
  console.log('Deploy TX:', tx);

  const receipt = await client.waitForTransactionReceipt({
    hash: tx, waitUntil: 'finalized', retries: 250, interval: 4000,
  });
  const addr = receipt?.txDataDecoded?.contractAddress;
  console.log('result:', receipt?.resultName, '| exec:', receipt?.txExecutionResultName);
  console.log('ADDR:', addr);

  if (addr) {
    fs.writeFileSync('/home/administrator/freelance-arbitration/addr.txt', addr);
    await new Promise(x => setTimeout(x, 8000));
    try {
      const c = await client.getContractCode(addr);
      console.log('code stored:', (c || '').length, 'bytes');
    } catch (e) { console.log('code check err:', (e.shortMessage || e.message).slice(0, 60)); }
  }
}

main().catch((e) => { console.error('FAIL:', e.message); process.exit(1); });
