class KeyController {
  constructor(keyService) {
    this._keyService = keyService;
  }

  publish = async (req, res, next) => {
    try {
      // Destructure explicitly so callers can't slip extra fields
      // (e.g. userId) into the service call via req.body spreading.
      const { publicKey, keyType, acknowledgeRotation } = req.body;
      const result = await this._keyService.publishKey({
        userId: req.user.id,
        publicKey,
        keyType,
        acknowledgeRotation,
      });
      const statusCode = result.status === 'pinned' ? 201 : 200;
      res.status(statusCode).json({ data: result });
    } catch (err) {
      next(err);
    }
  };

  getKey = async (req, res, next) => {
    try {
      const keys = await this._keyService.getPublicKeys(req.params.userId);
      res.json({ data: keys });
    } catch (err) {
      next(err);
    }
  };

  listKeys = async (_req, res, next) => {
    try {
      const keys = await this._keyService.listPublicKeys();
      res.json({ data: keys });
    } catch (err) {
      next(err);
    }
  };

  getHistory = async (req, res, next) => {
    try {
      const history = await this._keyService.getKeyHistory(
        req.params.userId,
        req.params.keyType
      );
      res.json({ data: history });
    } catch (err) {
      next(err);
    }
  };
}

module.exports = KeyController;
