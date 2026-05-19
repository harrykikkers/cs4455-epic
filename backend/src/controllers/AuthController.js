/**
 * Controllers are thin — they parse the HTTP request, call the
 * appropriate service method, and format the HTTP response.
 * No business logic lives here.
 */
class AuthController {
  constructor(authService) {
    this._authService = authService;
  }

  register = async (req, res, next) => {
    try {
      const user = await this._authService.register(req.body);
      res.status(201).json({ data: user });
    } catch (err) {
      next(err);
    }
  };

  login = async (req, res, next) => {
    try {
      const result = await this._authService.login(req.body);
      res.json({ data: result });
    } catch (err) {
      next(err);
    }
  };

  me = async (req, res) => {
    // req.user is set by auth middleware
    res.json({ data: req.user });
  };
}

module.exports = AuthController;
