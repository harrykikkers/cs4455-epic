class KeyController {
  constructor(keyService) {
    this._keyService = keyService;
  }

  publish = async (req, res, next) => {
    try {
      const { publicKey, keyType } = req.body;
      const result = await this._keyService.publishKey({
        userId: req.user.id,
        publicKey,
        keyType,
      });
      res.status(201).json({
        data: {
          message: result.rotated ? 'Public key rotated' : 'Public key published',
          rotated: result.rotated,
          previousKey: result.previousKey,
        },
      });
    } catch (err) {
      next(err);
    }
  };

  getKey = async (req, res, next) => {
    try {
      const key = await this._keyService.getPublicKey(req.params.userId);
      res.json({ data: key });
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
}

module.exports = KeyController;
