module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['@typescript-eslint', 'react-hooks', 'jsx-a11y'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
    'plugin:jsx-a11y/recommended',
  ],
  ignorePatterns: ['dist', 'node_modules', '*.cjs', '*.config.*'],
  rules: {
    // Money and probabilities are formatted through src/lib/format.ts only.
    // Raw toFixed in a component is how "$120.5" ships to a customer-facing screen.
    'no-restricted-properties': [
      'error',
      { object: 'Number', property: 'toFixed', message: 'Use lib/format.ts helpers.' },
    ],
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/consistent-type-imports': 'warn',
  },
}
