const { JSDOM } = require('jsdom');
const fs = require('fs');

const html = fs.readFileSync('frontend/profile.html', 'utf-8');

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable"
});

dom.window.console.error = function(...args) {
  console.log("VUE ERROR:", ...args);
};

setTimeout(() => {
  console.log("Done");
}, 2000);
