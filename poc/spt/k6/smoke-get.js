import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '30s',
};

export default function () {
  const url = __ENV.POC_TARGET_URL || 'https://httpbin.org/get';
  http.get(url);
  sleep(1);
}
