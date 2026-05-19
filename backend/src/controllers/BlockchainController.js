class BlockchainController {
  constructor(blockchainService) {
    this._blockchainService = blockchainService;
  }

  verify = async (req, res, next) => {
    try {
      const result = await this._blockchainService.verifyDigest(req.body.content);
      res.json({ data: result });
    } catch (err) {
      next(err);
    }
  };
}

module.exports = BlockchainController;
