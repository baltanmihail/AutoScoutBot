const fs = require('fs');
const content = fs.readFileSync('frontend/profile.html', 'utf-8');
const { parse } = require('@vue/compiler-dom');
try {
  parse(content);
  console.log("No template errors");
} catch (e) {
  console.log(e);
}
