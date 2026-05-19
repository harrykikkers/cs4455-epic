class KeyController {
  constructor(keyService) {
    this._keyService = keyService;
  }

  publish = async (req, res, next) => {
    try {
      await this._keyService.publishKey({
        userId: req.user.id,
        ...req.body,
      });
      res.status(201).json({ data: { message: 'Public key published' } });
    } catch (err) {
      next(err);
    }
  };

  getKeys = async (req, res, next) => {
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
}

module.exports = KeyController;