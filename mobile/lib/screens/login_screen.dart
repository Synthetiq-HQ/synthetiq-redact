import 'package:flutter/material.dart';
import '../theme.dart';
import 'main_shell.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailCtrl = TextEditingController(text: 'officer@hillingdon.gov.uk');
  final _passCtrl = TextEditingController(text: 'demo1234');
  bool _obscure = true;
  bool _loading = false;

  void _login() async {
    if (_emailCtrl.text.isEmpty || _passCtrl.text.isEmpty) return;
    setState(() => _loading = true);
    await Future.delayed(const Duration(milliseconds: 800));
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const MainShell()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 40),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(height: 24),

              // Logo + branding
              Center(
                child: Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    color: kPrimary.withOpacity(0.15),
                    shape: BoxShape.circle,
                    border: Border.all(color: kPrimary, width: 2),
                  ),
                  child: const Icon(Icons.shield_outlined, color: kPrimary, size: 42),
                ),
              ),
              const SizedBox(height: 20),
              const Center(
                child: Text(
                  'ClearDoc',
                  style: TextStyle(
                    color: kTextPrimary,
                    fontSize: 32,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.5,
                  ),
                ),
              ),
              const SizedBox(height: 6),
              const Center(
                child: Text(
                  'Secure Document Redaction',
                  style: TextStyle(color: kTextSecondary, fontSize: 14),
                ),
              ),
              const SizedBox(height: 48),

              // Demo quick-login chips
              const Text(
                'QUICK LOGIN',
                style: TextStyle(
                  color: kTextSecondary,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  _QuickChip(
                    label: 'Officer',
                    onTap: () {
                      _emailCtrl.text = 'officer@hillingdon.gov.uk';
                      _passCtrl.text = 'demo1234';
                    },
                  ),
                  const SizedBox(width: 8),
                  _QuickChip(
                    label: 'Reviewer',
                    onTap: () {
                      _emailCtrl.text = 'reviewer@hillingdon.gov.uk';
                      _passCtrl.text = 'demo5678';
                    },
                  ),
                  const SizedBox(width: 8),
                  _QuickChip(
                    label: 'Admin',
                    onTap: () {
                      _emailCtrl.text = 'admin@hillingdon.gov.uk';
                      _passCtrl.text = 'admin0000';
                    },
                  ),
                ],
              ),
              const SizedBox(height: 28),

              // Email field
              TextField(
                controller: _emailCtrl,
                keyboardType: TextInputType.emailAddress,
                style: const TextStyle(color: kTextPrimary),
                decoration: const InputDecoration(
                  labelText: 'Email address',
                  prefixIcon: Icon(Icons.email_outlined, color: kTextSecondary, size: 20),
                ),
              ),
              const SizedBox(height: 14),

              // Password field
              TextField(
                controller: _passCtrl,
                obscureText: _obscure,
                style: const TextStyle(color: kTextPrimary),
                decoration: InputDecoration(
                  labelText: 'Password',
                  prefixIcon: const Icon(Icons.lock_outline, color: kTextSecondary, size: 20),
                  suffixIcon: IconButton(
                    icon: Icon(
                      _obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                      color: kTextSecondary,
                      size: 20,
                    ),
                    onPressed: () => setState(() => _obscure = !_obscure),
                  ),
                ),
                onSubmitted: (_) => _login(),
              ),
              const SizedBox(height: 8),

              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () {},
                  child: const Text(
                    'Forgot password?',
                    style: TextStyle(color: kPrimary, fontSize: 13),
                  ),
                ),
              ),
              const SizedBox(height: 20),

              // Sign in button
              SizedBox(
                height: 52,
                child: ElevatedButton(
                  onPressed: _loading ? null : _login,
                  child: _loading
                      ? const SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('Sign In'),
                ),
              ),
              const SizedBox(height: 48),

              // Footer
              const Center(
                child: Text(
                  'Hillingdon Council x Brunel University\nDemo — Synthetic data only',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: kTextSecondary, fontSize: 12, height: 1.6),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _QuickChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _QuickChip({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: kPrimary.withOpacity(0.12),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: kPrimary.withOpacity(0.4)),
        ),
        child: Text(label, style: const TextStyle(color: kPrimary, fontSize: 13)),
      ),
    );
  }
}
