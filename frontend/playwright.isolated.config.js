import {defineConfig} from '@playwright/test';
import base from './playwright.config.js';

// Run the existing full suite without stopping an operator's 5173/8000 servers.
process.env.OSA_TEST_PORT_OFFSET='10';
export default defineConfig({...base,outputDir:'test-results/regression',timeout:180000,expect:{timeout:15000},webServer:base.webServer.map(server=>{
  const url=new URL(server.url);
  const port=Number(url.port);
  url.port=String(port+10);
  let command=server.command;
  if(port===5173 || port===4173) command+=` -- --port ${port+10}`;
  if(command.includes(`--port ${port}`)) command=command.replace(`--port ${port}`,`--port ${port+10}`);
  return {...server,command,url:url.toString(),env:{...server.env,
    OSA_BACKEND_URL:'http://127.0.0.1:8011',OSA_TEST_PORT:'8011',OSA_BASELINE_PORT:'5184',APP_ENV:'development',
  }};
})});
