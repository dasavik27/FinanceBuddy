/**
 * @deprecated Prefer AccountSetupPrompt — kept so older imports keep working.
 * PAN-only setup when password is not required.
 */
import AccountSetupPrompt from './AccountSetupPrompt'

export default function MandatoryPanPrompt() {
  return (
    <AccountSetupPrompt
      requirePassword={false}
      requirePan
      onPasswordComplete={() => {}}
    />
  )
}
