// sign_runner.js —— 生成抖音直播 wss 连接所需的 signature
// 用法: node sign_runner.js <md5_hex>
// 输出: 仅打印 signature 字符串（stdout）
const fs = require('fs');
const path = require('path');

function main() {
    const md5 = process.argv[2];
    if (!md5) {
        process.stderr.write('missing md5 argument');
        process.exit(2);
    }
    const signPath = path.join(__dirname, 'sign.js');
    const code = fs.readFileSync(signPath, 'utf-8');
    // sign.js 会在全局作用域给 crawler 赋值并定义 get_sign
    eval(code);
    const sig = get_sign(md5);
    process.stdout.write(String(sig));
}

main();
