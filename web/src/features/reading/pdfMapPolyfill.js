function install(prototype) {
  if (typeof prototype.getOrInsert !== "function") {
    Object.defineProperty(prototype, "getOrInsert", {
      configurable: true,
      writable: true,
      value(key, value) {
        if (!this.has(key)) this.set(key, value);
        return this.get(key);
      },
    });
  }
  if (typeof prototype.getOrInsertComputed !== "function") {
    Object.defineProperty(prototype, "getOrInsertComputed", {
      configurable: true,
      writable: true,
      value(key, callback) {
        if (!this.has(key)) this.set(key, callback(key));
        return this.get(key);
      },
    });
  }
}

install(Map.prototype);
install(WeakMap.prototype);
