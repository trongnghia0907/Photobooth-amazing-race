import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
const html = readFileSync(new URL('../../osa_booth_photobooth.html',import.meta.url));
createServer((req,res)=>{res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(html);}).listen(5174,'127.0.0.1');
