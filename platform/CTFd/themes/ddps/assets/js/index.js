import CTFd from "@ctfdio/ctfd-js";
import { Modal } from "bootstrap";

import dayjs from "dayjs";
import advancedFormat from "dayjs/plugin/advancedFormat";

import times from "./theme/times";
import styles from "./theme/styles";
import highlight from "./theme/highlight";

import alerts from "./utils/alerts";
import tooltips from "./utils/tooltips";
import collapse from "./utils/collapse";

import eventAlerts from "./utils/notifications/alerts";
import eventToasts from "./utils/notifications/toasts";
import eventRead from "./utils/notifications/read";

import "./components/language";

dayjs.extend(advancedFormat);
CTFd.init(window.init);

const originalFetch = CTFd.fetch;
CTFd.fetch = async (url, options) => {
  const response = await originalFetch(url, options);
  if (response.status === 401) {
    const modalElement = document.getElementById("session-expired-modal");
    if (modalElement) {
      const modal = new Modal(modalElement);
      modal.show();
    }
  }
  return response;
};

(() => {
  styles();
  times();
  highlight();

  alerts();
  tooltips();
  collapse();

  eventRead();
  eventAlerts();
  eventToasts();
})();

export default CTFd;
