import {build} from 'esbuild';
import {mkdir,copyFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('.',import.meta.url));
await mkdir(new URL('dist/',import.meta.url),{recursive:true});
await build({absWorkingDir:root,entryPoints:['src/main.jsx'],bundle:true,minify:true,outfile:'dist/main.js',
  define:{'process.env.NODE_ENV':'"production"'},target:['safari15'],legalComments:'eof'});
await copyFile(new URL('src/index.html',import.meta.url),new URL('dist/index.html',import.meta.url));
