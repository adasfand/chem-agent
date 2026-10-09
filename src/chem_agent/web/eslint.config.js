import js from '@eslint/js'
import ts from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

export default ts.config(
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'app.js'] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...vue.configs['flat/essential'],
  { files: ['**/*.ts', '**/*.vue'], rules: { 'no-undef': 'off' } },
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: ts.parser, extraFileExtensions: ['.vue'] } },
    rules: { 'vue/multi-word-component-names': 'off' },
  },
)
