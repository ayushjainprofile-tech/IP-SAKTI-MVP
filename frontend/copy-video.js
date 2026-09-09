import fs from 'fs';
import path from 'path';

const src = path.resolve('landing-page/bacground white white sheet.mp4');
const dst1 = path.resolve('src/white-sheet-bg.mp4');
const dst2 = path.resolve('landing-page/hero-bg-video.mp4');

fs.copyFileSync(src, dst1);
fs.copyFileSync(src, dst2);
console.log('Successfully copied white sheet video!');
