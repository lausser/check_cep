const TEST_START_TIME = Date.now();

function getTimestamp() {
  return `+${Date.now() - TEST_START_TIME}ms`;
}

function cepLog(message) {
  console.log(`[CEP${getTimestamp()}] ${message}`);
}

function cepLogLocated(target) {
  cepLog(`located element: ${target}`);
}

function cepLogFound(value) {
  cepLog(`located string: ${value}`);
}

function cepLogType(target, value) {
  cepLog(`typing string into ${target}: ${value}`);
}

function cepLogPress(target) {
  cepLog(`pressing button/link/option: ${target}`);
}

function cepLogWait(durationMs, reason) {
  cepLog(`waiting ${durationMs}ms ${reason}`);
}

function cepLogUrl(page) {
  cepLog(`current page url is ${page.url()}`);
}

module.exports = {
  getTimestamp,
  cepLog,
  cepLogLocated,
  cepLogFound,
  cepLogType,
  cepLogPress,
  cepLogWait,
  cepLogUrl,
};
