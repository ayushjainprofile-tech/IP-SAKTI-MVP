import fs from 'fs';
import path from 'path';

const rishiMuniSrc = path.resolve('landing-page/watermark-removed-Ek_Rishi_Muni_kuchh_Granth_lik.mp4');
const whiteSheetSrc = path.resolve('landing-page/bacground white white sheet.mp4');

const rishiMuniDst = path.resolve('src/rishi-muni-bg.mp4');
const whiteSheetDst = path.resolve('src/white-sheet-bg.mp4');

fs.copyFileSync(rishiMuniSrc, rishiMuniDst);
fs.copyFileSync(whiteSheetSrc, whiteSheetDst);
console.log('Successfully copied both Rishi Muni and White Sheet videos!');
