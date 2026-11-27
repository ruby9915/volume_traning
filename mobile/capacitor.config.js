// 볼륨 트래커 안드로이드 앱 설정.
// 앱은 화면을 담고 있지 않고, 아래 주소의 서버가 내려 주는 웹 화면을 그대로 띄운다.
// 그래서 웹을 배포하면 앱도 바로 최신이 되고, 서버 주소가 바뀌면 여기만 고쳐 다시 빌드하면 된다.
//
// 다른 서버로 시험할 때(예: 에뮬레이터에서 이 PC의 테스트 서버):
//   PowerShell:  $env:VT_SERVER_URL = "http://10.0.2.2:8010"; npx cap sync android
const fs = require("fs");
const path = require("path");

const SERVER_URL = process.env.VT_SERVER_URL || "https://volume.tail6df393.ts.net";

// 오프라인 안내 화면: "다시 시도"가 돌아갈 주소를 넣어 www/offline.html 로 만든다.
// (서버 주소를 여는 방식에서는 안내 화면 한 장만 앱 안에서 읽히므로, 주소를 별도 파일로 둘 수 없다)
const offline = fs.readFileSync(path.join(__dirname, "offline.template.html"), "utf8");
fs.writeFileSync(path.join(__dirname, "www", "offline.html"), offline.replaceAll("__SERVER_URL__", SERVER_URL));

/** @type {import('@capacitor/cli').CapacitorConfig} */
module.exports = {
  appId: "com.volumetracker.app",
  appName: "볼륨 트래커",
  webDir: "www",
  server: {
    url: SERVER_URL,
    cleartext: SERVER_URL.startsWith("http://"), // https가 아닌 주소는 시험용으로만
    errorPath: "offline.html", // 서버에 닿지 못하면 앱에 든 안내 화면을 보여 준다
  },
  plugins: {
    // 상태바·키보드 여백은 MainActivity 가 직접 준다
    SystemBars: { insetsHandling: "disable" },
  },
};
