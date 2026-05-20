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

  changePassword = async (req, res, next) => {
    try {
      await this._authService.changePassword({
        userId: req.user.id,
        currentPassword: req.body.currentPassword,
        newPassword: req.body.newPassword,
      });
      res.json({ data: { message: 'Password changed' } });
    } catch (err) {
      next(err);
    }
  };

  async me(req, res, next) {
  try {
    const user = await this._authService.getUserProfile(req.user.id);
    res.json({ data: user });
  } catch (err) {
    next(err);
  }
}
}

module.exports = AuthController;